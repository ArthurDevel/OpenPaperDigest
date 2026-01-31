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
    schedule="0 0 * * *",  # Daily at midnight UTC
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

    **Schedule:** Daily at midnight UTC

    **Parameters:**
    - `dry_run` (default: False): If True, runs analysis and compression but doesn't save to database.
      Set to True for testing without persisting changes.

    **Configuration (hardcoded constants):**
    - Max figure size threshold: 100 KB
    - Target width: 800px (maintains aspect ratio)
    - WebP quality: 85%
    - Batch size: 20 papers per commit

    **What it does:**
    1. Scans all completed papers with processed_content
    2. Parses the JSON and identifies figures larger than 100 KB
    3. Compresses them to WebP at 800px width and 85% quality
    4. Only replaces if compressed version is smaller than original
    5. Updates the processed_content JSON in batches (unless dry_run=True)
    6. Generates a summary report with compression statistics

    **Expected results:**
    - 30-60% reduction in figure sizes (WebP is efficient for diagrams)
    - Significantly smaller processed_content JSON
    - Faster API responses when loading paper data
    - Preserves transparency for diagrams that need it

    **Safety:**
    - Only processes completed papers
    - Only replaces if compression actually reduces size
    - Batch commits for atomicity
    - Auto-rollback on errors
    - Can be re-run safely (skips already-compressed figures under threshold)
    - Use `dry_run=True` for testing without saving changes
    """,
)
def compress_oversized_figures_dag():

    @task
    def find_papers_with_oversized_figures() -> List[Dict[str, Any]]:
        """
        Find all papers with figures larger than MAX_SIZE_KB.

        Returns:
            List[Dict]: List of papers to process with metadata:
                - paper_uuid: UUID of the paper
                - oversized_figure_count: Number of oversized figures
                - total_oversized_kb: Total size of oversized figures in KB
        """
        print(f"Scanning for figures larger than {MAX_SIZE_KB} KB...")

        papers_to_process = []
        scan_batch_size = 50  # Process 50 papers at a time to avoid memory issues
        offset = 0
        total_scanned = 0

        with database_session() as session:
            # Get total count first (without loading content)
            total_count = session.query(PaperRecord).filter(
                PaperRecord.status == 'completed',
                PaperRecord.processed_content.isnot(None)
            ).count()

            print(f"Found {total_count} completed papers to scan")

            # Scan in batches to avoid loading all processed_content into memory
            while offset < total_count:
                papers = session.query(PaperRecord).filter(
                    PaperRecord.status == 'completed',
                    PaperRecord.processed_content.isnot(None)
                ).order_by(PaperRecord.id).offset(offset).limit(scan_batch_size).all()

                if not papers:
                    break

                batch_num = (offset // scan_batch_size) + 1
                total_batches = (total_count + scan_batch_size - 1) // scan_batch_size
                print(f"Scanning batch {batch_num}/{total_batches} ({len(papers)} papers)...")

                # Check each paper's figures
                for paper in papers:
                    total_scanned += 1
                    try:
                        content = json.loads(paper.processed_content)
                        figures = content.get("figures", [])

                        if not figures:
                            continue

                        oversized_count = 0
                        total_oversized_kb = 0

                        for figure in figures:
                            image_data_url = figure.get("image_data_url", "")
                            if not image_data_url or "base64," not in image_data_url:
                                continue

                            # Skip already-compressed WebP images
                            if image_data_url.startswith("data:image/webp"):
                                continue

                            base64_data = image_data_url.split("base64,", 1)[1]
                            size_kb = calculate_base64_size_kb(base64_data)

                            if size_kb > MAX_SIZE_KB:
                                oversized_count += 1
                                total_oversized_kb += size_kb

                        if oversized_count > 0:
                            papers_to_process.append({
                                'paper_uuid': paper.paper_uuid,
                                'oversized_figure_count': oversized_count,
                                'total_oversized_kb': round(total_oversized_kb, 2)
                            })

                    except Exception as e:
                        print(f"Error checking figures for {paper.paper_uuid}: {e}")
                        continue

                # Clear session to free memory after each batch
                session.expire_all()
                offset += scan_batch_size

        print(f"\nScanned {total_scanned} papers")
        print(f"Found {len(papers_to_process)} papers with oversized figures")

        if papers_to_process:
            total_figures = sum(p['oversized_figure_count'] for p in papers_to_process)
            total_size_mb = sum(p['total_oversized_kb'] for p in papers_to_process) / 1024
            print(f"Total oversized figures: {total_figures}")
            print(f"Total size to compress: {total_size_mb:.2f} MB")

            # Print sample of papers to process
            sample_size = min(5, len(papers_to_process))
            print(f"\nSample of papers to process (showing {sample_size}):")
            for paper in papers_to_process[:sample_size]:
                print(f"  - {paper['paper_uuid']}: {paper['oversized_figure_count']} figures, {paper['total_oversized_kb']} KB")

        return papers_to_process


    @task
    def compress_figures_batch(papers_to_process: List[Dict[str, Any]], **context) -> List[Dict[str, Any]]:
        """
        Compress figures in batches.

        Args:
            papers_to_process: List of papers from find_papers_with_oversized_figures
            context: Airflow context containing params

        Returns:
            List[Dict]: Compression statistics for each paper
        """
        # Get dry_run parameter from DAG params
        dry_run = context.get("params", {}).get("dry_run", True)

        if not papers_to_process:
            print("No figures to compress")
            return []

        mode_str = "DRY RUN" if dry_run else "LIVE"
        print(f"\n[{mode_str}] Starting compression of figures in {len(papers_to_process)} papers...")
        print(f"Configuration: {TARGET_WIDTH}px width, WebP {WEBP_QUALITY}% quality, batches of {BATCH_SIZE}")

        if dry_run:
            print("⚠️  DRY RUN MODE: Changes will NOT be saved to database")

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

                    try:
                        # Load paper record
                        paper = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()

                        if not paper or not paper.processed_content:
                            print(f"  ⚠️  {paper_uuid}: Content not found, skipping")
                            continue

                        # Parse JSON content
                        content = json.loads(paper.processed_content)
                        figures = content.get("figures", [])

                        if not figures:
                            print(f"  ⚠️  {paper_uuid}: No figures found, skipping")
                            continue

                        # Track stats for this paper
                        paper_stats = {
                            'paper_uuid': paper_uuid,
                            'figures_compressed': 0,
                            'original_total_kb': 0,
                            'compressed_total_kb': 0
                        }

                        # Compress each oversized figure
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

                            try:
                                # Decode, compress, and re-encode
                                image_bytes, _ = decode_data_url(image_data_url)
                                compressed_bytes, stats = compress_figure(image_bytes)

                                # Only use compressed version if it's actually smaller
                                if stats['new_size_kb'] < stats['original_size_kb']:
                                    new_data_url = encode_to_webp_data_url(compressed_bytes)

                                    # Update figure in content
                                    figures[i]["image_data_url"] = new_data_url

                                    # Update stats
                                    paper_stats['figures_compressed'] += 1
                                    paper_stats['original_total_kb'] += stats['original_size_kb']
                                    paper_stats['compressed_total_kb'] += stats['new_size_kb']
                                else:
                                    # Skip - compression made it larger
                                    paper_stats['figures_skipped'] = paper_stats.get('figures_skipped', 0) + 1

                            except Exception as e:
                                print(f"    ⚠️  Figure {i} in {paper_uuid}: Error - {e}")
                                continue

                        # Update content back to JSON (only if not dry run)
                        if not dry_run:
                            content["figures"] = figures
                            paper.processed_content = json.dumps(content, ensure_ascii=False)

                        # Calculate reduction
                        if paper_stats['original_total_kb'] > 0:
                            reduction = ((paper_stats['original_total_kb'] - paper_stats['compressed_total_kb'])
                                        / paper_stats['original_total_kb']) * 100
                            paper_stats['reduction_percent'] = round(reduction, 2)
                        else:
                            paper_stats['reduction_percent'] = 0

                        dry_marker = " [DRY RUN]" if dry_run else ""
                        print(f"  ✓ {paper_uuid}: {paper_stats['figures_compressed']} figures, "
                              f"{paper_stats['original_total_kb']:.1f}KB → {paper_stats['compressed_total_kb']:.1f}KB "
                              f"({paper_stats['reduction_percent']}% reduction){dry_marker}")

                        all_results.append(paper_stats)

                    except Exception as e:
                        print(f"  ✗ {paper_uuid}: Error - {e}")
                        continue

                # Commit batch (only if not dry run)
                if dry_run:
                    print(f"  [DRY RUN] Skipping commit for batch {batch_num}")
                    session.rollback()  # Discard any changes
                else:
                    print(f"  Committing batch {batch_num}...")

        if dry_run:
            print(f"\n✓ [DRY RUN] Analyzed {len(all_results)} papers (no changes saved)")
        else:
            print(f"\n✓ Successfully processed {len(all_results)} papers")
        return all_results


    @task
    def generate_summary_report(compression_results: List[Dict[str, Any]], **context) -> Dict[str, Any]:
        """
        Generate a summary report of compression results.

        Args:
            compression_results: List of compression statistics from compress_figures_batch
            context: Airflow context containing params

        Returns:
            Dict: Summary statistics
        """
        dry_run = context.get("params", {}).get("dry_run", True)

        if not compression_results:
            print("\nNo figures were compressed")
            return {
                'dry_run': dry_run,
                'total_papers_processed': 0,
                'total_figures_compressed': 0,
                'total_original_mb': 0,
                'total_compressed_mb': 0,
                'total_saved_mb': 0,
                'avg_reduction_percent': 0
            }

        # Calculate aggregate statistics
        total_papers = len(compression_results)
        total_figures = sum(r['figures_compressed'] for r in compression_results)
        total_original_kb = sum(r['original_total_kb'] for r in compression_results)
        total_compressed_kb = sum(r['compressed_total_kb'] for r in compression_results)
        total_saved_kb = total_original_kb - total_compressed_kb

        total_original_mb = total_original_kb / 1024
        total_compressed_mb = total_compressed_kb / 1024
        total_saved_mb = total_saved_kb / 1024

        avg_reduction_percent = (total_saved_kb / total_original_kb) * 100 if total_original_kb > 0 else 0

        # Find min/max reduction
        reductions = [r['reduction_percent'] for r in compression_results if r.get('reduction_percent')]
        min_reduction = min(reductions) if reductions else 0
        max_reduction = max(reductions) if reductions else 0

        # Print summary report
        mode_str = "[DRY RUN] " if dry_run else ""
        print("\n" + "=" * 60)
        print(f"{mode_str}FIGURE COMPRESSION SUMMARY REPORT")
        print("=" * 60)
        print(f"Mode:                       {'DRY RUN (no changes saved)' if dry_run else 'LIVE (changes saved)'}")
        print(f"Total papers processed:     {total_papers}")
        print(f"Total figures compressed:   {total_figures}")
        print(f"Total original size:        {total_original_mb:.2f} MB")
        print(f"Total compressed size:      {total_compressed_mb:.2f} MB")
        print(f"Total saved:                {total_saved_mb:.2f} MB")
        print(f"Average reduction:          {avg_reduction_percent:.2f}%")
        print(f"Min/Max reduction:          {min_reduction:.2f}% / {max_reduction:.2f}%")
        print("=" * 60)

        if dry_run:
            print("\n💡 To apply these changes, run again with dry_run=False")

        summary = {
            'dry_run': dry_run,
            'total_papers_processed': total_papers,
            'total_figures_compressed': total_figures,
            'total_original_mb': round(total_original_mb, 2),
            'total_compressed_mb': round(total_compressed_mb, 2),
            'total_saved_mb': round(total_saved_mb, 2),
            'avg_reduction_percent': round(avg_reduction_percent, 2),
            'min_reduction_percent': round(min_reduction, 2),
            'max_reduction_percent': round(max_reduction, 2)
        }

        return summary


    # Define task dependencies
    papers = find_papers_with_oversized_figures()
    results = compress_figures_batch(papers)
    summary = generate_summary_report(results)


# Instantiate the DAG
compress_oversized_figures_dag()
