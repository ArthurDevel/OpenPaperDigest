"""
Backfill embeddings for existing papers that have no embedding yet.

One-time Airflow DAG that generates 1536-dim embeddings via OpenRouter for all
completed papers where embedding IS NULL. Uses the summaries column to get the
five_minute_summary text; falls back to title-only if summaries is NULL.

Responsibilities:
- Find completed papers without embeddings
- Generate embeddings in batches via OpenRouter
- Update embedding column per paper with per-paper error handling
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

# ============================================================================
# CONSTANTS
# ============================================================================

BATCH_SIZE = 100

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


def fetch_papers_without_embeddings(batch_size: int = BATCH_SIZE) -> List[Dict]:
    """
    Query papers where status='completed' AND embedding IS NULL.

    Args:
        batch_size: Maximum number of papers to fetch.

    Returns:
        List[Dict]: List of dicts with paper_uuid, title, and summaries.
    """
    with database_session() as session:
        rows = session.query(
            PaperRecord.paper_uuid,
            PaperRecord.title,
            PaperRecord.summaries,
        ).filter(
            PaperRecord.status == 'completed',
            PaperRecord.embedding.is_(None),
        ).order_by(PaperRecord.id).limit(batch_size).all()

        return [
            {
                "paper_uuid": row.paper_uuid,
                "title": row.title,
                "summaries": row.summaries,
            }
            for row in rows
        ]


def generate_and_store_embeddings(papers: List[Dict]) -> int:
    """
    Generate embeddings for a batch of papers and update the database.

    For each paper, combines title + five_minute_summary (from summaries column)
    into embedding input. Falls back to title-only if no summary available.
    Per-paper error handling: logs failures, skips them, continues.

    Args:
        papers: List of paper dicts from fetch_papers_without_embeddings.

    Returns:
        int: Number of papers successfully updated.
    """
    from paperprocessor.embedding import generate_embedding

    updated = 0

    for paper in papers:
        paper_uuid = paper["paper_uuid"]
        title = paper["title"]

        try:
            # Extract summary from summaries JSON column
            summaries = paper.get("summaries") or {}
            summary = summaries.get("five_minute_summary")

            if not title:
                print(f"  SKIP {paper_uuid}: no title")
                continue

            # Generate embedding
            embedding = generate_embedding(title, summary)

            # Store in database
            with database_session() as session:
                record = session.query(PaperRecord).filter(
                    PaperRecord.paper_uuid == paper_uuid
                ).first()

                if record:
                    record.embedding = embedding
                    updated += 1

        except Exception as e:
            print(f"  FAIL {paper_uuid}: {e}")
            continue

    return updated


# ============================================================================
# DAG DEFINITION
# ============================================================================

@dag(
    dag_id="backfill_embeddings",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["papers", "maintenance", "backfill", "one-time"],
    doc_md="""
    ### Backfill Embeddings DAG

    **ONE-TIME USE DAG**: Generates 1536-dim embeddings via OpenRouter for all
    completed papers that have no embedding yet.

    **Why:** The feed recommendation system needs embeddings for ANN similarity
    search. Existing papers need embeddings backfilled so they appear in
    recommendation results.

    **Safety:**
    - Only processes papers where embedding IS NULL
    - Processes in batches of 100
    - Per-paper error handling (logs failures, skips, continues)
    - Can be re-run safely (idempotent - skips already-embedded papers)
    """,
)
def backfill_embeddings_dag():

    @task
    def find_papers() -> List[dict]:
        """
        Find papers that need embeddings generated.

        Returns:
            List[dict]: Papers with paper_uuid, title, and summaries.
        """
        print("Scanning for papers without embeddings...")
        papers = fetch_papers_without_embeddings(batch_size=BATCH_SIZE)
        print(f"Found {len(papers)} papers to process")
        return papers

    @task
    def process_batch(papers: List[dict]) -> Dict[str, int]:
        """
        Generate and store embeddings for a batch of papers.

        Args:
            papers: List of paper dicts to process.

        Returns:
            Dict with updated/total counts.
        """
        if not papers:
            print("No papers to process")
            return {"updated": 0, "total": 0}

        print(f"Processing {len(papers)} papers...")
        updated = generate_and_store_embeddings(papers)
        return {"updated": updated, "total": len(papers)}

    @task
    def generate_report(results: Dict[str, int]) -> None:
        """
        Print summary report of the backfill operation.

        Args:
            results: Counts from process_batch.
        """
        print("\n" + "=" * 50)
        print("BACKFILL EMBEDDINGS REPORT")
        print("=" * 50)
        print(f"Total papers:  {results['total']}")
        print(f"Updated:       {results['updated']}")
        print(f"Failed/Skipped: {results['total'] - results['updated']}")
        print("=" * 50)

    # Task dependencies
    papers = find_papers()
    results = process_batch(papers)
    generate_report(results)


backfill_embeddings_dag()
