"""
Backfill summaries column from processed_content.

Extracts five_minute_summary from the processed_content JSON blob and writes
it into the new summaries JSON column, one paper at a time to avoid OOM.

Responsibilities:
- Find papers with processed_content but no summaries
- Extract five_minute_summary one row at a time
- Update summaries column with commit per batch
- Generate summary report
"""

import sys
import json
import pendulum
from contextlib import contextmanager
from typing import List, Dict

from airflow.decorators import dag, task
from sqlalchemy.orm import Session

sys.path.insert(0, '/opt/airflow')

from shared.db import SessionLocal
from papers.db.models import PaperRecord

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

    **ONE-TIME USE DAG**: Extracts `five_minute_summary` from the `processed_content`
    JSON blob into the new `summaries` column for all existing papers.

    **Why:** The homepage fetches summaries for 20 papers on load. Previously each
    call read the full ~2MB `processed_content` blob just to extract one field.
    The new `summaries` column stores only the summary dict (~4KB), making reads fast.

    **Safety:**
    - Only processes papers where summaries IS NULL
    - Processes one paper at a time to avoid OOM (processed_content is ~2MB per row)
    - Batch commits every 5 papers
    - Can be re-run safely (skips already-backfilled rows)
    """,
)
def backfill_summaries_dag():

    @task
    def find_papers_to_backfill() -> List[int]:
        """
        Find paper IDs that need summaries backfilled.
        Only fetches IDs to keep memory low.

        Returns:
            List[int]: Paper IDs to process
        """
        print("Scanning for papers without summaries...")

        with database_session() as session:
            rows = session.query(PaperRecord.id).filter(
                PaperRecord.status == 'completed',
                PaperRecord.processed_content.isnot(None),
                PaperRecord.summaries.is_(None),
            ).order_by(PaperRecord.id).all()

            paper_ids = [row[0] for row in rows]

        print(f"Found {len(paper_ids)} papers to backfill")
        return paper_ids

    @task
    def backfill_batch(paper_ids: List[int]) -> Dict[str, int]:
        """
        Backfill summaries one paper at a time in small batches.

        Loads processed_content for a single row, extracts five_minute_summary,
        writes to summaries column, then moves on. Commits every BATCH_SIZE rows.

        Args:
            paper_ids: List of paper IDs to process

        Returns:
            Dict with backfilled/skipped/failed counts
        """
        if not paper_ids:
            print("No papers to backfill")
            return {"backfilled": 0, "skipped": 0, "failed": 0}

        total = len(paper_ids)
        backfilled = 0
        skipped = 0
        failed = 0

        print(f"Processing {total} papers in batches of {BATCH_SIZE}...")

        for batch_start in range(0, total, BATCH_SIZE):
            batch = paper_ids[batch_start:batch_start + BATCH_SIZE]

            with database_session() as session:
                for paper_id in batch:
                    try:
                        paper = session.query(PaperRecord).filter(
                            PaperRecord.id == paper_id
                        ).first()

                        if not paper or not paper.processed_content:
                            skipped += 1
                            session.expunge_all()
                            continue

                        content = json.loads(paper.processed_content)
                        five_minute_summary = content.get("five_minute_summary")

                        if five_minute_summary:
                            paper.summaries = {"five_minute_summary": five_minute_summary}
                            backfilled += 1
                        else:
                            skipped += 1

                        # Free memory before next row
                        session.expunge_all()

                    except (json.JSONDecodeError, TypeError) as e:
                        print(f"  SKIP id={paper_id}: {e}")
                        failed += 1
                        session.expunge_all()
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
    paper_ids = find_papers_to_backfill()
    results = backfill_batch(paper_ids)
    generate_report(results)


backfill_summaries_dag()
