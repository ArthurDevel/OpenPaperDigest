import sys
import pendulum
import base64
import io
import json
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Tuple, Any

from airflow.decorators import dag, task
from airflow.models import Param
from sqlalchemy.orm import Session

# Add project root to Python path to find shared modules
sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord

# Try to import PIL, provide helpful error if missing
try:
    from PIL import Image
except ImportError:
    raise ImportError(
        "Pillow is required for figure compression. "
        "Install with: pip install Pillow"
    )


### CONSTANTS ###

MAX_SIZE_KB = 100          # Only compress figures larger than 100 KB
TARGET_WIDTH = 800         # Resize to 800px width (maintains aspect ratio)
WEBP_QUALITY = 85          # Compression quality (85 is good balance)
BATCH_SIZE = 20            # Process 20 papers per batch (fewer since more work per paper)


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


def decode_data_url(data_url: str) -> Tuple[bytes, str]:
    """
    Extract and decode base64 data from a data URL.

    Args:
        data_url: Data URL string (e.g., "data:image/png;base64,...")

    Returns:
        Tuple[bytes, str]: (decoded image bytes, original mime type)

    Raises:
        ValueError: If data URL format is invalid
    """
    if not data_url or "base64," not in data_url:
        raise ValueError("Invalid data URL format")

    # Extract mime type
    mime_type = "image/png"  # default
    if data_url.startswith("data:"):
        mime_part = data_url.split(";")[0]
        mime_type = mime_part[5:]  # Remove "data:" prefix

    # Extract base64 portion after "base64,"
    base64_data = data_url.split("base64,", 1)[1]

    # Decode base64 to bytes
    return base64.b64decode(base64_data), mime_type


def encode_to_webp_data_url(image_bytes: bytes) -> str:
    """
    Encode image bytes to a WebP data URL.

    Args:
        image_bytes: Raw image bytes

    Returns:
        str: Data URL string (e.g., "data:image/webp;base64,...")
    """
    base64_str = base64.b64encode(image_bytes).decode('utf-8')
    return f"data:image/webp;base64,{base64_str}"


def compress_figure(image_bytes: bytes) -> Tuple[bytes, Dict[str, Any]]:
    """
    Compress and resize a figure image to WebP format.

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

    # WebP supports transparency, so just convert palette mode to RGBA
    if resized_image.mode == 'P':
        resized_image = resized_image.convert('RGBA')
    elif resized_image.mode == 'LA':
        resized_image = resized_image.convert('RGBA')

    # Compress as WebP
    output_buffer = io.BytesIO()
    resized_image.save(output_buffer, format='WEBP', quality=WEBP_QUALITY, method=6)
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
    dag_id="compress_oversized_figures",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 1 * * *",  # Daily at 1 AM UTC
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "optimization"],
    params={
        "dry_run": Param(
            default=False,
            type="boolean",
            description="If True, analyze and compress figures but don't save changes to database"
        ),
    },
    doc_md="""
    ### Compress Oversized Figures DAG

    Finds and compresses large figure images embedded in processed_content JSON.

    **Schedule:** Daily at 1 AM UTC

    **Parameters:**
    - `dry_run` (default: False): If True, runs analysis and compression but doesn't save to database.
      Set to True for testing without persisting changes.

    **Configuration (hardcoded constants):**
    - Max figure size threshold: 100 KB
    - Target width: 800px (maintains aspect ratio)
    - WebP quality: 85%
    - Batch size: 50 papers per task

    **Architecture:**
    1. `calculate_batches`: Counts papers, returns list of offsets for parallel processing
    2. `process_batch` (parallel): Each task scans and compresses its batch of papers
    3. `generate_summary`: Aggregates results from all batch tasks

    **What it does:**
    1. Calculates batch offsets based on total completed papers
    2. Each batch task scans its range of papers for oversized figures (>100 KB)
    3. Compresses them to WebP at 800px width and 85% quality
    4. Only replaces if compressed version is smaller than original
    5. Updates the processed_content JSON (unless dry_run=True)
    6. Generates a summary report with compression statistics

    **Expected results:**
    - 30-60% reduction in figure sizes (WebP is efficient for diagrams)
    - Significantly smaller processed_content JSON
    - Faster API responses when loading paper data
    - Preserves transparency for diagrams that need it

    **Safety:**
    - Only processes completed papers
    - Only replaces if compression actually reduces size
    - Each batch is a separate task (debuggable in UI)
    - Auto-rollback on errors within each batch
    - Can be re-run safely (skips already-compressed figures under threshold)
    - Use `dry_run=True` for testing without saving changes
    """,
)
def compress_oversized_figures_dag():

    @task
    def calculate_batches() -> List[int]:
        """
        Count completed papers and return list of batch offsets.

        Returns:
            List[int]: List of offsets for parallel batch processing
        """
        with database_session() as session:
            total_count = session.query(PaperRecord).filter(
                PaperRecord.status == 'completed',
                PaperRecord.processed_content.isnot(None)
            ).count()

        print(f"Found {total_count} completed papers to process")

        if total_count == 0:
            return []

        # Generate list of offsets
        offsets = list(range(0, total_count, BATCH_SIZE))
        print(f"Created {len(offsets)} batches of up to {BATCH_SIZE} papers each")

        return offsets

    @task
    def process_batch(offset: int, **context) -> Dict[str, Any]:
        """
        Scan and compress oversized figures for a batch of papers.

        Args:
            offset: Starting offset for this batch
            context: Airflow context containing params

        Returns:
            Dict: Batch statistics
        """
        dry_run = context.get("params", {}).get("dry_run", False)
        mode_str = "DRY RUN" if dry_run else "LIVE"

        print(f"[{mode_str}] Processing batch at offset {offset} (up to {BATCH_SIZE} papers)")
        print(f"Configuration: {TARGET_WIDTH}px width, WebP {WEBP_QUALITY}% quality, threshold {MAX_SIZE_KB}KB")

        batch_stats = {
            'offset': offset,
            'papers_scanned': 0,
            'papers_with_oversized': 0,
            'figures_compressed': 0,
            'figures_skipped': 0,
            'original_total_kb': 0,
            'compressed_total_kb': 0,
        }

        with database_session() as session:
            papers = session.query(PaperRecord).filter(
                PaperRecord.status == 'completed',
                PaperRecord.processed_content.isnot(None)
            ).order_by(PaperRecord.id).offset(offset).limit(BATCH_SIZE).all()

            if not papers:
                print(f"No papers found at offset {offset}")
                return batch_stats

            print(f"Scanning {len(papers)} papers...")

            for paper in papers:
                batch_stats['papers_scanned'] += 1

                try:
                    content = json.loads(paper.processed_content)
                    figures = content.get("figures", [])

                    if not figures:
                        continue

                    paper_had_oversized = False
                    paper_modified = False

                    for i, figure in enumerate(figures):
                        image_data_url = figure.get("image_data_url", "")
                        if not image_data_url or "base64," not in image_data_url:
                            continue

                        # Skip already-compressed WebP images
                        if image_data_url.startswith("data:image/webp"):
                            continue

                        base64_data = image_data_url.split("base64,", 1)[1]
                        size_kb = calculate_base64_size_kb(base64_data)

                        if size_kb <= MAX_SIZE_KB:
                            continue

                        paper_had_oversized = True

                        try:
                            # Decode, compress, and re-encode
                            image_bytes, _ = decode_data_url(image_data_url)
                            compressed_bytes, stats = compress_figure(image_bytes)

                            # Only use compressed version if it's actually smaller
                            if stats['new_size_kb'] < stats['original_size_kb']:
                                new_data_url = encode_to_webp_data_url(compressed_bytes)
                                figures[i]["image_data_url"] = new_data_url
                                paper_modified = True

                                batch_stats['figures_compressed'] += 1
                                batch_stats['original_total_kb'] += stats['original_size_kb']
                                batch_stats['compressed_total_kb'] += stats['new_size_kb']

                                print(f"  ✓ {paper.paper_uuid} fig[{i}]: "
                                      f"{stats['original_size_kb']:.1f}KB → {stats['new_size_kb']:.1f}KB "
                                      f"({stats['reduction_percent']:.1f}% reduction)")
                            else:
                                batch_stats['figures_skipped'] += 1
                                print(f"  ⊘ {paper.paper_uuid} fig[{i}]: skipped (compression increased size)")

                        except Exception as e:
                            print(f"  ⚠️ {paper.paper_uuid} fig[{i}]: Error - {e}")
                            continue

                    if paper_had_oversized:
                        batch_stats['papers_with_oversized'] += 1

                    # Update content if modified and not dry run
                    if paper_modified and not dry_run:
                        content["figures"] = figures
                        paper.processed_content = json.dumps(content, ensure_ascii=False)

                except Exception as e:
                    print(f"  ✗ {paper.paper_uuid}: Error - {e}")
                    continue

            # Commit or rollback
            if dry_run:
                print(f"[DRY RUN] Rolling back changes for batch at offset {offset}")
                session.rollback()
            else:
                print(f"Committing changes for batch at offset {offset}")

        # Calculate reduction percentage
        if batch_stats['original_total_kb'] > 0:
            reduction = ((batch_stats['original_total_kb'] - batch_stats['compressed_total_kb'])
                        / batch_stats['original_total_kb']) * 100
            batch_stats['reduction_percent'] = round(reduction, 2)
        else:
            batch_stats['reduction_percent'] = 0

        print(f"\nBatch summary: {batch_stats['papers_scanned']} scanned, "
              f"{batch_stats['papers_with_oversized']} with oversized, "
              f"{batch_stats['figures_compressed']} compressed, "
              f"{batch_stats['figures_skipped']} skipped")

        return batch_stats

    @task
    def generate_summary(batch_results: List[Dict[str, Any]], **context) -> Dict[str, Any]:
        """
        Generate a summary report from all batch results.

        Args:
            batch_results: List of batch statistics from process_batch tasks
            context: Airflow context containing params

        Returns:
            Dict: Summary statistics
        """
        dry_run = context.get("params", {}).get("dry_run", False)

        # Filter out empty results
        results = [r for r in batch_results if r.get('papers_scanned', 0) > 0]

        if not results:
            print("\nNo papers were processed")
            return {
                'dry_run': dry_run,
                'total_batches': 0,
                'total_papers_scanned': 0,
                'total_papers_with_oversized': 0,
                'total_figures_compressed': 0,
                'total_original_mb': 0,
                'total_compressed_mb': 0,
                'total_saved_mb': 0,
                'avg_reduction_percent': 0
            }

        # Aggregate statistics
        total_batches = len(results)
        total_papers_scanned = sum(r['papers_scanned'] for r in results)
        total_papers_with_oversized = sum(r['papers_with_oversized'] for r in results)
        total_figures_compressed = sum(r['figures_compressed'] for r in results)
        total_figures_skipped = sum(r.get('figures_skipped', 0) for r in results)
        total_original_kb = sum(r['original_total_kb'] for r in results)
        total_compressed_kb = sum(r['compressed_total_kb'] for r in results)
        total_saved_kb = total_original_kb - total_compressed_kb

        total_original_mb = total_original_kb / 1024
        total_compressed_mb = total_compressed_kb / 1024
        total_saved_mb = total_saved_kb / 1024

        avg_reduction_percent = (total_saved_kb / total_original_kb) * 100 if total_original_kb > 0 else 0

        # Print summary report
        mode_str = "[DRY RUN] " if dry_run else ""
        print("\n" + "=" * 60)
        print(f"{mode_str}FIGURE COMPRESSION SUMMARY REPORT")
        print("=" * 60)
        print(f"Mode:                       {'DRY RUN (no changes saved)' if dry_run else 'LIVE (changes saved)'}")
        print(f"Total batches:              {total_batches}")
        print(f"Total papers scanned:       {total_papers_scanned}")
        print(f"Papers with oversized:      {total_papers_with_oversized}")
        print(f"Figures compressed:         {total_figures_compressed}")
        print(f"Figures skipped:            {total_figures_skipped}")
        print(f"Total original size:        {total_original_mb:.2f} MB")
        print(f"Total compressed size:      {total_compressed_mb:.2f} MB")
        print(f"Total saved:                {total_saved_mb:.2f} MB")
        print(f"Average reduction:          {avg_reduction_percent:.2f}%")
        print("=" * 60)

        if dry_run:
            print("\n💡 To apply these changes, run again with dry_run=False")

        return {
            'dry_run': dry_run,
            'total_batches': total_batches,
            'total_papers_scanned': total_papers_scanned,
            'total_papers_with_oversized': total_papers_with_oversized,
            'total_figures_compressed': total_figures_compressed,
            'total_figures_skipped': total_figures_skipped,
            'total_original_mb': round(total_original_mb, 2),
            'total_compressed_mb': round(total_compressed_mb, 2),
            'total_saved_mb': round(total_saved_mb, 2),
            'avg_reduction_percent': round(avg_reduction_percent, 2),
        }


    # Define task dependencies with dynamic task mapping
    offsets = calculate_batches()
    batch_results = process_batch.expand(offset=offsets)
    summary = generate_summary(batch_results)


# Instantiate the DAG
compress_oversized_figures_dag()
