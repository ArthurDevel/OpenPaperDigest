"""
DEPRECATED: This DAG is no longer needed. New papers (pipeline v2) do not
store figures.

Compress oversized figure images in Supabase Storage.

Scans all completed papers, downloads figure images from storage, compresses
oversized ones to WebP, and re-uploads the compressed versions.

Responsibilities:
- Iterate through papers in batches to manage memory
- Download and check size of each figure from storage
- Compress oversized figures to WebP format
- Re-upload compressed figures to storage
- Update figures.json metadata
- Generate compression report
"""

import sys
import io
import json
import pendulum
from contextlib import contextmanager
from typing import Dict, Any

from airflow.decorators import dag, task
from airflow.models import Param
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord
import papers.storage as storage

try:
    from PIL import Image
except ImportError:
    raise ImportError(
        "Pillow is required for figure compression. "
        "Install with: pip install Pillow"
    )


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_SIZE_KB = 100          # Only compress figures larger than 100 KB
TARGET_WIDTH = 800         # Resize to 800px width (maintains aspect ratio)
WEBP_QUALITY = 85          # Compression quality (85 is good balance)
BATCH_SIZE = 20            # Process 20 papers per batch


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


def compress_figure(image_bytes: bytes) -> tuple:
    """
    Compress and resize a figure image to WebP format.

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

    if resized_image.mode == 'P':
        resized_image = resized_image.convert('RGBA')
    elif resized_image.mode == 'LA':
        resized_image = resized_image.convert('RGBA')

    output_buffer = io.BytesIO()
    resized_image.save(output_buffer, format='WEBP', quality=WEBP_QUALITY, method=6)
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
    dag_id="compress_oversized_figures",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule="0 1 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "optimization"],
    params={
        "dry_run": Param(
            default=False,
            type="boolean",
            description="If True, analyze figures but don't save compressed versions"
        ),
    },
    doc_md="""
    ### Compress Oversized Figures DAG

    **DEPRECATED**: This DAG is no longer needed. New papers (pipeline v2) do
    not store figures.

    Finds and compresses large figure images stored in Supabase Storage.

    **Schedule:** Daily at 1 AM UTC

    **Parameters:**
    - `dry_run` (default: False): If True, runs analysis only.

    **Configuration:**
    - Max figure size threshold: 100 KB
    - Target width: 800px (maintains aspect ratio)
    - WebP quality: 85%
    - Batch size: 20 papers per batch

    **What it does:**
    1. Iterates through papers in batches
    2. Downloads figures.json to find figure identifiers
    3. Downloads each figure image from storage, checks size
    4. Compresses oversized figures to WebP
    5. Re-uploads compressed figures to storage
    6. Generates a summary report
    """,
)
def compress_oversized_figures_dag():

    @task
    def process_all_batches(**context) -> Dict[str, Any]:
        """
        Process all papers serially in batches.

        Downloads figures from storage, compresses oversized ones, re-uploads.

        Returns:
            Dict: Aggregated statistics from all batches
        """
        dry_run = context.get("params", {}).get("dry_run", False)
        mode_str = "DRY RUN" if dry_run else "LIVE"

        print(f"[{mode_str}] Starting serial batch processing")
        print(f"Configuration: {TARGET_WIDTH}px width, WebP {WEBP_QUALITY}% quality, threshold {MAX_SIZE_KB}KB")

        total_stats = {
            'total_batches': 0,
            'papers_scanned': 0,
            'papers_with_oversized': 0,
            'figures_compressed': 0,
            'figures_skipped': 0,
            'original_total_kb': 0,
            'compressed_total_kb': 0,
        }

        # Get list of completed paper UUIDs
        with database_session() as session:
            paper_uuids = [
                row[0] for row in
                session.query(PaperRecord.paper_uuid).filter(
                    PaperRecord.status == 'completed',
                ).order_by(PaperRecord.id).all()
            ]

        total_count = len(paper_uuids)
        print(f"Found {total_count} completed papers to process")

        if total_count == 0:
            return total_stats

        num_batches = (total_count + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"Will process in {num_batches} batches\n")

        bucket = storage._bucket()

        for batch_idx in range(0, total_count, BATCH_SIZE):
            batch = paper_uuids[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = (batch_idx // BATCH_SIZE) + 1

            print(f"\n{'='*50}")
            print(f"[{mode_str}] Processing batch {batch_num}/{num_batches}")
            print(f"{'='*50}")

            batch_compressed = 0
            batch_skipped = 0

            for paper_uuid in batch:
                total_stats['papers_scanned'] += 1

                try:
                    # Download figures.json to get figure identifiers
                    figures_bytes = bucket.download(f"{paper_uuid}/figures.json")
                    figures_meta = json.loads(figures_bytes.decode("utf-8"))

                    if not figures_meta:
                        continue

                    paper_had_oversized = False

                    for fig in figures_meta:
                        identifier = fig.get("identifier")
                        if not identifier:
                            continue

                        # Download figure image
                        try:
                            fig_path = f"{paper_uuid}/figures/{identifier}.png"
                            image_bytes = bucket.download(fig_path)
                        except Exception:
                            continue

                        size_kb = len(image_bytes) / 1024

                        if size_kb <= MAX_SIZE_KB:
                            continue

                        paper_had_oversized = True

                        try:
                            compressed_bytes, stats = compress_figure(image_bytes)

                            if stats['new_size_kb'] < stats['original_size_kb']:
                                if not dry_run:
                                    # Re-upload as WebP
                                    webp_path = f"{paper_uuid}/figures/{identifier}.png"
                                    bucket.upload(
                                        webp_path,
                                        compressed_bytes,
                                        {"content-type": "image/webp", "upsert": "true"},
                                    )

                                total_stats['figures_compressed'] += 1
                                total_stats['original_total_kb'] += stats['original_size_kb']
                                total_stats['compressed_total_kb'] += stats['new_size_kb']
                                batch_compressed += 1

                                print(f"  [x] {paper_uuid} {identifier}: "
                                      f"{stats['original_size_kb']:.1f}KB -> {stats['new_size_kb']:.1f}KB "
                                      f"({stats['reduction_percent']:.1f}% reduction)")
                            else:
                                total_stats['figures_skipped'] += 1
                                batch_skipped += 1

                        except Exception as e:
                            print(f"  [!] {paper_uuid} {identifier}: Error - {e}")
                            continue

                    if paper_had_oversized:
                        total_stats['papers_with_oversized'] += 1

                except Exception as e:
                    print(f"  [X] {paper_uuid}: Error - {e}")
                    continue

            total_stats['total_batches'] += 1
            print(f"Batch {batch_num} complete: {batch_compressed} compressed, {batch_skipped} skipped")

        if total_stats['original_total_kb'] > 0:
            reduction = ((total_stats['original_total_kb'] - total_stats['compressed_total_kb'])
                        / total_stats['original_total_kb']) * 100
            total_stats['reduction_percent'] = round(reduction, 2)
        else:
            total_stats['reduction_percent'] = 0

        print(f"\n{'='*50}")
        print(f"All batches complete!")
        print(f"Total: {total_stats['papers_scanned']} scanned, "
              f"{total_stats['papers_with_oversized']} with oversized, "
              f"{total_stats['figures_compressed']} compressed")
        print(f"{'='*50}")

        return total_stats

    @task
    def generate_summary(stats: Dict[str, Any], **context) -> Dict[str, Any]:
        """
        Generate a summary report from processing stats.

        Args:
            stats: Statistics from process_all_batches

        Returns:
            Dict: Summary statistics
        """
        dry_run = context.get("params", {}).get("dry_run", False)

        if stats.get('papers_scanned', 0) == 0:
            print("\nNo papers were processed")
            return {}

        total_original_kb = stats.get('original_total_kb', 0)
        total_compressed_kb = stats.get('compressed_total_kb', 0)
        total_saved_kb = total_original_kb - total_compressed_kb

        mode_str = "[DRY RUN] " if dry_run else ""
        print("\n" + "=" * 60)
        print(f"{mode_str}FIGURE COMPRESSION SUMMARY REPORT")
        print("=" * 60)
        print(f"Mode:                       {'DRY RUN' if dry_run else 'LIVE'}")
        print(f"Total batches:              {stats.get('total_batches', 0)}")
        print(f"Total papers scanned:       {stats.get('papers_scanned', 0)}")
        print(f"Papers with oversized:      {stats.get('papers_with_oversized', 0)}")
        print(f"Figures compressed:         {stats.get('figures_compressed', 0)}")
        print(f"Figures skipped:            {stats.get('figures_skipped', 0)}")
        print(f"Total original size:        {total_original_kb / 1024:.2f} MB")
        print(f"Total compressed size:      {total_compressed_kb / 1024:.2f} MB")
        print(f"Total saved:                {total_saved_kb / 1024:.2f} MB")
        print(f"Average reduction:          {stats.get('reduction_percent', 0):.2f}%")
        print("=" * 60)

        return stats

    stats = process_all_batches()
    summary = generate_summary(stats)


compress_oversized_figures_dag()
