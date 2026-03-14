"""
Backfill summaries column from Supabase Storage metadata.

Downloads metadata.json from storage for each paper that has no summaries column
populated, extracts five_minute_summary, and writes it to the summaries column.

Responsibilities:
- Find papers with status=completed but no summaries
- Download metadata from storage one paper at a time
- Update summaries column with commit per batch
- Generate summary report
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
# CONSTANTS
# ============================================================================

BATCH_SIZE = 5


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
    dag_id="backfill_summaries",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time"],
    doc_md="""
    ### Backfill Summaries DAG

    **ONE-TIME USE DAG**: Extracts `five_minute_summary` from storage metadata
    into the `summaries` column for all existing papers.

    **Why:** The homepage fetches summaries for 20 papers on load. The `summaries`
    column stores only the summary dict (~4KB), making reads fast.

    **Safety:**
    - Only processes papers where summaries IS NULL
    - Processes one paper at a time to avoid OOM
    - Batch commits every 5 papers
    - Can be re-run safely (skips already-backfilled rows)
    """,
)
def backfill_summaries_dag():

    @task
    def find_papers_to_backfill() -> List[str]:
        """
        Find paper UUIDs that need summaries backfilled.
        Only fetches UUIDs to keep memory low.

        Returns:
            List[str]: Paper UUIDs to process
        """
        print("Scanning for papers without summaries...")

        with database_session() as session:
            rows = session.query(PaperRecord.paper_uuid).filter(
                PaperRecord.status == 'completed',
                PaperRecord.summaries.is_(None),
            ).order_by(PaperRecord.id).all()

            paper_uuids = [row[0] for row in rows]

        print(f"Found {len(paper_uuids)} papers to backfill")
        return paper_uuids

    @task
    def backfill_batch(paper_uuids: List[str]) -> Dict[str, int]:
        """
        Backfill summaries one paper at a time in small batches.

        Downloads metadata.json from storage, extracts five_minute_summary,
        writes to summaries column. Commits every BATCH_SIZE rows.

        Args:
            paper_uuids: List of paper UUIDs to process

        Returns:
            Dict with backfilled/skipped/failed counts
        """
        if not paper_uuids:
            print("No papers to backfill")
            return {"backfilled": 0, "skipped": 0, "failed": 0}

        total = len(paper_uuids)
        backfilled = 0
        skipped = 0
        failed = 0

        print(f"Processing {total} papers in batches of {BATCH_SIZE}...")

        for batch_start in range(0, total, BATCH_SIZE):
            batch = paper_uuids[batch_start:batch_start + BATCH_SIZE]

            with database_session() as session:
                for paper_uuid in batch:
                    try:
                        # Download metadata from storage
                        stored = storage.download_paper_content(paper_uuid)
                        metadata = stored.metadata
                        # The five_minute_summary may be in metadata or not
                        # In legacy format it was at the top level of processed_content
                        # In storage it should be in metadata.json or already in summaries
                        # Note: v2 papers (pipeline_version=2) won't have five_minute_summary
                        # in metadata -- summaries are generated on-demand via web API
                        five_minute_summary = metadata.get("five_minute_summary")

                        if not five_minute_summary:
                            skipped += 1
                            continue

                        paper = session.query(PaperRecord).filter(
                            PaperRecord.paper_uuid == paper_uuid
                        ).first()

                        if not paper:
                            skipped += 1
                            continue

                        paper.summaries = {"five_minute_summary": five_minute_summary}
                        backfilled += 1

                    except Exception as e:
                        print(f"  SKIP uuid={paper_uuid}: {e}")
                        failed += 1
                        continue

            processed = batch_start + len(batch)
            print(f"  [{processed}/{total}] backfilled={backfilled}, skipped={skipped}, failed={failed}")

        return {"backfilled": backfilled, "skipped": skipped, "failed": failed}

    @task
    def generate_report(results: Dict[str, int]) -> None:
        """
        Print summary report of the backfill operation.

        Args:
            results: Counts from backfill_batch
        """
        print("\n" + "=" * 50)
        print("BACKFILL SUMMARIES REPORT")
        print("=" * 50)
        print(f"Backfilled: {results['backfilled']}")
        print(f"Skipped:    {results['skipped']}")
        print(f"Failed:     {results['failed']}")
        print("=" * 50)

    # Task dependencies
    paper_uuids = find_papers_to_backfill()
    results = backfill_batch(paper_uuids)
    generate_report(results)


backfill_summaries_dag()
